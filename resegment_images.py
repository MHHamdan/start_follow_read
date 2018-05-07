import sys
import torch
from torch.utils.data import DataLoader
from torch.autograd import Variable
import yaml
from utils.dataset_parse import load_file_list
from e2e import alignment_dataset
from e2e.alignment_dataset import AlignmentDataset
import numpy as np
from utils import transformation_utils
import cv2

def main():

    config_path = sys.argv[1]

    with open(config_path) as f:
        config = yaml.load(f)

    for dataset_lookup in ['training_set', 'validation_set']:
        set_list = load_file_list(config['training'][dataset_lookup])
        dataset = AlignmentDataset(set_list, None)
        dataloader = DataLoader(dataset, batch_size=1, shuffle=False, num_workers=0, collate_fn=alignment_dataset.collate)

        output_grid_size = config['network']['hw']['input_height']
        t = ((np.arange(output_grid_size) + 0.5) / float(output_grid_size))[:,None].astype(np.float32)
        t = np.repeat(t,axis=1, repeats=output_grid_size)
        t = Variable(torch.from_numpy(t), requires_grad=False, volatile=True)
        s = t.t()

        t = t[:,:,None]
        s = s[:,:,None]

        interpolations = torch.cat([
            (1-t)*s,
            (1-t)*(1-s),
            t*s,
            t*(1-s),
        ], dim=-1)

        for l in dataloader:
            for l_i in l:
                img = Variable(l_i['full_img'], requires_grad=False, volatile=True)

                img_np = l_i['full_img'].numpy()[0,...].transpose([2,1,0])
                img_np = ((img_np+1)*128).astype(np.uint8)
                img_np = img_np.copy()

                renorm_matrix = transformation_utils.compute_renorm_matrix(img)
                expanded_renorm_matrix = renorm_matrix.expand(1,3,3)

                print l_i['img_key']

                for item in l_i['gt_json']:

                    if 'lf' not in item or 'hw_path' not in item:
                        continue

                    hw_path = item['hw_path']

                    lf_pts = item['lf']
                    if 'after_lf' in item:
                        lf_pts += item['after_lf']


                    lf_path = []
                    for i, step in enumerate(lf_pts):
                        x0 = step['x0']
                        x1 = step['x1']
                        y0 = step['y0']
                        y1 = step['y1']

                        pt = torch.Tensor([[x1,x0],[y1,y0],[1,1]])[None,...]
                        pt = Variable(pt, requires_grad=False, volatile=True)
                        lf_path.append(pt)

                    grid_line = []
                    for i in xrange(0, len(lf_path)-1):
                        pts_0 = lf_path[i]
                        pts_1 = lf_path[i+1]
                        pts = torch.cat([pts_0, pts_1], dim=2)

                        grid_pts = expanded_renorm_matrix.bmm(pts)

                        grid = interpolations[None,:,:,None,:] * grid_pts[:,None,None,:,:]
                        grid = grid.sum(dim=-1)[...,:2]

                        grid_line.append(grid)

                    grid_line = torch.cat(grid_line, dim=1)

                    line = torch.nn.functional.grid_sample(img.transpose(2,3), grid_line)
                    line = line.transpose(2,3)

                    line = line[0].transpose(0,1).transpose(1,2)
                    line = (line + 1)*128
                    l_np = line.data.cpu().numpy()

                    cv2.imwrite(hw_path, l_np)

if __name__ == "__main__":
    main()